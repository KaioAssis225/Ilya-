import type { OptionalChoiceInput } from '../types'
import { cartStorageKey, notifyCartChanged } from './cart'

/** O que a Transferência precisa saber de uma linha do Estoque para montar a linha do orçamento. */
export interface ShowroomCartSource {
  item_id: string
  product_code: string
  optional_choices: Array<{
    application_id: string | null
    category_code: string
    optional_id: string | null
    optional_name: string
    custom?: boolean
  }>
}

/** Converte os opcionais do Estoque nos campos do carrinho: por aplicação (inclusive Customizado) ou, no seletor antigo, por categoria. */
export function showroomChoicesToCart(choices: ShowroomCartSource['optional_choices']) {
  const optionalChoices: OptionalChoiceInput[] = []
  const legacy: Record<string, string> = {}
  for (const choice of choices) {
    if (choice.application_id) {
      optionalChoices.push(choice.custom
        ? { application_id: choice.application_id, custom_text: '' }
        : { application_id: choice.application_id, optional_id: choice.optional_id })
    } else {
      legacy[choice.category_code] = choice.optional_name
    }
  }
  return { optional_choices: optionalChoices, opt_categories: legacy }
}

/**
 * Leva a peça do Estoque para a aba Novo orçamento: acrescenta uma linha ao
 * rascunho (carrinho) do usuário. NADA sai do estoque aqui: a linha carrega
 * `showroom_source_item_id` e o servidor só baixa o saldo quando o orçamento é
 * salvo. Desistir (limpar o carrinho ou fechar a aba) não tira nada da box.
 */
export function addShowroomItemToCart(
  userId: string,
  source: ShowroomCartSource,
  quantity: number,
  boxName: string,
  market: 'BR' | 'EU' = 'EU',
): void {
  const key = cartStorageKey(userId, market)
  let lines: unknown[] = []
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(key) ?? '[]')
    if (Array.isArray(parsed)) lines = parsed
  } catch {
    lines = []
  }
  lines.push({
    line_id: crypto.randomUUID(),
    product_code: source.product_code,
    qty: quantity,
    discount: 0,
    attachments: [],
    ...showroomChoicesToCart(source.optional_choices),
    showroom_source_item_id: source.item_id,
    showroom_box_name: boxName,
  })
  localStorage.setItem(key, JSON.stringify(lines))
  notifyCartChanged()
}
