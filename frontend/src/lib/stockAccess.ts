import type { UserRole } from '../hooks/useUsers'

/**
 * Regra do login único com o Estoque Brasil, espelhada só para a tela de
 * administração decidir se mostra o checkbox. A decisão real é do servidor
 * (422 quando a conta não é elegível): aqui é apenas conveniência de uso.
 */
const STOCK_BLOCKED_ROLES: ReadonlyArray<string> = ['cliente', 'benchmark_readonly']

/**
 * Mesma regra, lida dos vínculos por mercado (tela da Plataforma): precisa de um
 * vínculo BR ativo com papel permitido e nenhum vínculo com papel bloqueado.
 */
export function canGrantStockAccessToAccesses(
  accesses: ReadonlyArray<{ market_code: 'BR' | 'EU'; role: UserRole | string; status: string }> | undefined,
): boolean {
  if (!accesses) return false
  if (accesses.some(access => STOCK_BLOCKED_ROLES.includes(access.role))) return false
  return accesses.some(access => access.market_code === 'BR' && access.status === 'active')
}

export function canGrantStockAccess(
  allowedMarkets: ReadonlyArray<'BR' | 'EU'> | undefined,
  role: UserRole | string | undefined,
): boolean {
  if (!allowedMarkets?.includes('BR')) return false
  return !STOCK_BLOCKED_ROLES.includes(role ?? '')
}
