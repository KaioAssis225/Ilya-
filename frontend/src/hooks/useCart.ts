import { useEffect, useState } from 'react'
import { CART_EVENT, readCartQuantities } from '../lib/cart'

/**
 * Quantidade por SKU no carrinho, reagindo a mudanças na própria aba
 * (CustomEvent disparado por quem escreve) e em outras abas (evento `storage`).
 *
 * Não usa `useSyncExternalStore`: o snapshot é um objeto novo a cada leitura, o
 * que dispararia loop infinito sem uma camada de cache que não vale o custo aqui.
 */
export function useCartQuantities(): Record<string, number> {
  const [quantities, setQuantities] = useState<Record<string, number>>(readCartQuantities)

  useEffect(() => {
    const sync = () => setQuantities(readCartQuantities())
    // Reconcilia no mount: o carrinho pode ter mudado entre o estado inicial e
    // a montagem (ex.: outra rota escreveu durante o lazy-load desta página).
    sync()
    window.addEventListener(CART_EVENT, sync)
    window.addEventListener('storage', sync)
    return () => {
      window.removeEventListener(CART_EVENT, sync)
      window.removeEventListener('storage', sync)
    }
  }, [])

  return quantities
}
