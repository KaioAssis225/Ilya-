// Fonte única da chave do carrinho e do sinal de "carrinho mudou".
//
// O carrinho vive em localStorage e é escrito por duas telas (catálogo e
// orçamento) sem nenhum estado React compartilhado. Para o contador do nav
// reagir sem prop drilling nem store nova, quem escreve chama
// `notifyCartChanged()`; quem exibe escuta pelo hook `useCartQuantities`.
//
// O evento `storage` do navegador NÃO cobre isso sozinho: ele só dispara em
// OUTRAS abas, nunca na aba que fez a escrita. Daí o CustomEvent próprio.

export const CART_KEY = 'carrinho_orcamento'
export const CART_EVENT = 'ilya:cart-changed'

type StoredCartItem = { product_code: string; qty: number }

/** Quantidade por SKU: `{ IAC0000: 2 }`. Vazio se não houver carrinho ou o JSON estiver corrompido. */
export function readCartQuantities(): Record<string, number> {
  try {
    const raw = localStorage.getItem(CART_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return {}

    const quantities: Record<string, number> = {}
    for (const item of parsed as StoredCartItem[]) {
      if (!item || typeof item.product_code !== 'string') continue
      const qty = Number(item.qty)
      if (!Number.isFinite(qty) || qty <= 0) continue
      quantities[item.product_code] = qty
    }
    return quantities
  } catch {
    return {}
  }
}

/** Total de UNIDADES (não de produtos distintos), igual à barra do orçamento. */
export function countCartUnits(quantities: Record<string, number>): number {
  return Object.values(quantities).reduce((total, qty) => total + qty, 0)
}

export function notifyCartChanged() {
  window.dispatchEvent(new Event(CART_EVENT))
}
