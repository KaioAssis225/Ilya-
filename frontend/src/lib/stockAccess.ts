import type { UserRole } from '../hooks/useUsers'

/**
 * Regra do login único com o Estoque Brasil, espelhada só para a tela de
 * administração decidir se mostra o checkbox. A decisão real é do servidor
 * (422 quando a conta não é elegível): aqui é apenas conveniência de uso.
 */
const STOCK_BLOCKED_ROLES: ReadonlyArray<string> = ['cliente', 'benchmark_readonly']

export function canGrantStockAccess(
  allowedMarkets: ReadonlyArray<'BR' | 'EU'> | undefined,
  role: UserRole | string | undefined,
): boolean {
  if (!allowedMarkets?.includes('BR')) return false
  return !STOCK_BLOCKED_ROLES.includes(role ?? '')
}
