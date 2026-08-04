// Fonte única da chave do carrinho e do sinal de "carrinho mudou".
//
// O carrinho vive em localStorage e é escrito por duas telas (catálogo e
// orçamento) sem nenhum estado React compartilhado. Cada usuário recebe uma
// chave própria para que trocar de login no mesmo browser nunca compartilhe um
// orçamento em andamento.
//
// O evento `storage` do navegador NÃO cobre isso sozinho: ele só dispara em
// OUTRAS abas, nunca na aba que fez a escrita. Daí o CustomEvent próprio.

const CART_KEY_PREFIX = 'carrinho_orcamento'
export const CART_EVENT = 'ilya:cart-changed'

type StoredCartItem = { product_code: string; qty: number }

/** Quantidade por SKU: `{ IAC0000: 2 }`. Vazio se não houver carrinho ou o JSON estiver corrompido. */
export function cartStorageKey(userId: string): string {
  return `${CART_KEY_PREFIX}:${userId}`
}

/** Remove o formato antigo, que era compartilhado entre todas as contas. */
export function removeUnsafeLegacyCart(): void {
  localStorage.removeItem(CART_KEY_PREFIX)
}

export function readCartQuantities(userId?: string | null): Record<string, number> {
  if (!userId) return {}
  try {
    const raw = localStorage.getItem(cartStorageKey(userId))
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
