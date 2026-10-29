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
const CART_PRICE_LIST_KEY_PREFIX = 'carrinho_orcamento_tabela_preco'
export const CART_EVENT = 'ilya:cart-changed'
export type PriceListCode = 'lojista' | 'arquiteto' | 'corporativo' | 'pvp'

type StoredCartItem = { product_code: string; qty: number; sold_by_area?: boolean; area_pieces?: number }
export type CartQuantity = { qty: number; sold_by_area: boolean; area_pieces?: number }

/** Quantidade por SKU: `{ IAC0000: 2 }`. Vazio se não houver carrinho ou o JSON estiver corrompido. */
export function cartStorageKey(userId: string, market: 'BR' | 'EU' = 'BR'): string {
  return `${CART_KEY_PREFIX}:${userId}:${market}`
}

export function cartPriceListStorageKey(userId: string, market: 'BR' | 'EU'): string {
  return `${CART_PRICE_LIST_KEY_PREFIX}:${userId}:${market}`
}

export function readCartPriceList(userId?: string | null, market: 'BR' | 'EU' = 'BR'): PriceListCode | null {
  if (!userId) return null
  const value = localStorage.getItem(cartPriceListStorageKey(userId, market))
  return value === 'lojista' || value === 'arquiteto' || value === 'corporativo' || value === 'pvp'
    ? value
    : null
}

export function writeCartPriceList(userId: string, market: 'BR' | 'EU', value: PriceListCode): void {
  localStorage.setItem(cartPriceListStorageKey(userId, market), value)
}

export function removeCartPriceList(userId: string, market: 'BR' | 'EU'): void {
  localStorage.removeItem(cartPriceListStorageKey(userId, market))
}

/**
 * Chave da fronteira privada (ADR 0002): identidade + mercado ativo.
 *
 * `PrivateApp` a usa como `key` do `LocaleProvider` e do
 * `PrivateSessionBoundary`, então trocar de mercado desmonta a árvore inteira e
 * descarta cache, mutations e estado local das páginas. Vive aqui, ao lado da
 * chave do carrinho, porque as duas precisam concordar: um cache novo com o
 * carrinho antigo mostraria itens do mercado anterior.
 */
export function privateScopeKey(userId: string, market: 'BR' | 'EU'): string {
  return `${userId}:${market}`
}

export function configureProductPath(productCode: string): string {
  return `/orcamentos?configure=${encodeURIComponent(productCode)}`
}

/** Remove o formato antigo, que era compartilhado entre todas as contas. */
export function removeUnsafeLegacyCart(): void {
  localStorage.removeItem(CART_KEY_PREFIX)
  localStorage.removeItem(CART_PRICE_LIST_KEY_PREFIX)
}

export function readCartQuantities(userId?: string | null, market: 'BR' | 'EU' = 'BR'): Record<string, CartQuantity> {
  if (!userId) return {}
  try {
    const raw = localStorage.getItem(cartStorageKey(userId, market))
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return {}

    const quantities: Record<string, CartQuantity> = {}
    for (const item of parsed as StoredCartItem[]) {
      if (!item || typeof item.product_code !== 'string') continue
      const qty = Number(item.qty)
      if (!Number.isFinite(qty) || qty <= 0) continue
      const areaPieces = Number(item.area_pieces)
      const validAreaPieces = Number.isFinite(areaPieces) && areaPieces >= 1 ? areaPieces : undefined
      quantities[item.product_code] = {
        qty,
        sold_by_area: item.sold_by_area === true,
        ...(validAreaPieces !== undefined ? { area_pieces: validAreaPieces } : {}),
      }
    }
    return quantities
  } catch {
    return {}
  }
}

/** Total de UNIDADES (não de produtos distintos), igual à barra do orçamento. */
export function countCartUnits(quantities: Record<string, number | CartQuantity>): number {
  return Object.values(quantities).reduce<number>((total, entry) => {
    if (typeof entry === 'number') return total + entry
    return total + (entry.sold_by_area ? (entry.area_pieces ?? 1) : entry.qty)
  }, 0)
}

export function notifyCartChanged() {
  window.dispatchEvent(new Event(CART_EVENT))
}
